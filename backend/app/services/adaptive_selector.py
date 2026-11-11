"""Shared task/action scorers, real CPU weight fitting and safe JSON inference."""
from copy import deepcopy
import importlib.metadata
import json
import math
from pathlib import Path
import time
import warnings

import numpy as np
import psutil
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from backend.app.schemas.adaptive import ModelBundle
from backend.app.services.adaptive_skills import FEATURES,FEATURE_VERSION,EMBEDDING_VERSION
from backend.app.services.learning_engine import RUNTIME_IDENTITY,digest


def compatibility():
    return {'policy':RUNTIME_IDENTITY,'feature_version':FEATURE_VERSION,'embedding_version':EMBEDDING_VERSION,
            'numpy':importlib.metadata.version('numpy'),'sklearn':importlib.metadata.version('scikit-learn')}


class RulesScorer:
    name='rules-memory-v1'

    def score(self,problem_context,candidate_skill,decision_features):
        from backend.app.services.adaptive_skills import baseline_score
        return {'score':baseline_score(candidate_skill),'model_version':self.name}


class JsonScorer:
    """Never unpickle a model. Validate topology, finite values and provenance."""
    def __init__(self,bundle,expected_hash=None):
        if expected_hash and digest(bundle)!=expected_hash:
            raise ValueError('MODEL_INTEGRITY_FAILED')
        self.bundle=ModelBundle.model_validate(bundle)
        if self.bundle.feature_schema!=FEATURES or self.bundle.feature_version!=FEATURE_VERSION or self.bundle.embedding_version!=EMBEDDING_VERSION:
            raise ValueError('FEATURE_OR_EMBEDDING_VERSION_MISMATCH')
        if self.bundle.compatibility.get('runtime')!=compatibility():
            raise ValueError('MODEL_RUNTIME_MISMATCH')
        weights=self.bundle.weights;biases=self.bundle.biases
        if len(weights)!=len(biases) or not 1<=len(weights)<=3:
            raise ValueError('MODEL_TOPOLOGY_INVALID')
        sizes=[len(FEATURES)];self.weights=[];self.biases=[];count=0
        for matrix,bias in zip(weights,biases):
            w=np.asarray(matrix,dtype=np.float64);b=np.asarray(bias,dtype=np.float64)
            if w.ndim!=2 or b.ndim!=1 or w.shape!=(sizes[-1],len(b)) or not 1<=len(b)<=128:
                raise ValueError('MODEL_TOPOLOGY_INVALID')
            if not np.isfinite(w).all() or not np.isfinite(b).all():
                raise ValueError('NONFINITE_MODEL')
            count+=w.size+b.size;sizes.append(len(b));self.weights.append(w);self.biases.append(b)
        if sizes[-1]!=1 or count>30000 or self.bundle.kind=='linear' and len(weights)!=1:
            raise ValueError('MODEL_TOPOLOGY_INVALID')
        self.mean=np.asarray(self.bundle.preprocessing['mean'],dtype=float)
        self.scale=np.asarray(self.bundle.preprocessing['scale'],dtype=float)
        if self.mean.shape!=(len(FEATURES),) or self.scale.shape!=self.mean.shape or not np.isfinite(self.mean).all() or not np.isfinite(self.scale).all() or (self.scale<=0).any():
            raise ValueError('PREPROCESSING_INVALID')
        self.name=f'{self.bundle.kind}:{digest(bundle)[:16]}'

    def score(self,problem_context,candidate_skill,decision_features):
        if candidate_skill.implementation_hash not in self.bundle.compatibility['trained_implementation_hashes']:
            raise ValueError('COLD_START_SKILL')
        return {'score':float(self.logits([decision_features])[0]),'model_version':self.name}

    def logits(self,features):
        x=np.asarray(features,dtype=np.float64)
        if x.ndim!=2 or x.shape[1]!=len(FEATURES) or not np.isfinite(x).all():
            raise ValueError('FEATURE_VECTOR_INVALID')
        x=(x-self.mean)/self.scale
        for index,(weight,bias) in enumerate(zip(self.weights,self.biases)):
            x=x@weight+bias
            if index<len(self.weights)-1:
                x=np.maximum(x,0)
        return np.clip(x[:,0],-50,50)


def sigmoid(logits):
    return 1/(1+np.exp(-np.clip(np.asarray(logits,dtype=float),-50,50)))


def fit_models(train_x,train_y,development_x,development_y,manifest,implementation_hashes,seed=17,max_epochs=120,deadline_seconds=120):
    """Fit only train preprocessing; tune/stop on the explicitly grouped dev set."""
    started=time.perf_counter();deadline=time.monotonic()+deadline_seconds
    process=psutil.Process();rss_start=process.memory_info().rss;rss_peak=rss_start
    x=np.asarray(train_x,dtype=np.float64);y=np.asarray(train_y,dtype=np.int64)
    dev=np.asarray(development_x,dtype=np.float64);dy=np.asarray(development_y,dtype=np.int64)
    if x.ndim!=2 or x.shape[1]!=len(FEATURES) or set(y.tolist())!={0,1} or len(dev)!=len(dy):
        raise ValueError('TRAINING_DATA_INSUFFICIENT')
    scaler=StandardScaler().fit(x)
    tx=scaler.transform(x);dx=scaler.transform(dev)
    common={'format':'repair-scorer-json-v1','preprocessing':{'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist()},
        'feature_schema':FEATURES,'feature_version':FEATURE_VERSION,'embedding_version':EMBEDDING_VERSION,
        'training_manifest':manifest,'label_policy':'independent-action-postconditions-v1',
        'compatibility':{'runtime':compatibility(),'trained_implementation_hashes':sorted(set(implementation_hashes))},
        'calibration_status':'unavailable'}
    bundles={};trials=[]
    with threadpool_limits(limits=1):
        linear_trials=[]
        for regularization in (.1,1.0):
            if time.monotonic()>deadline:
                raise TimeoutError('TRAINING_DEADLINE')
            model=LogisticRegression(C=regularization,solver='liblinear',random_state=seed,max_iter=200)
            model.fit(tx,y)
            loss=float(log_loss(dy,model.predict_proba(dx),labels=[0,1]))
            linear_trials.append((loss,model,regularization))
        loss,linear,c=min(linear_trials,key=lambda item:item[0])
        bundles['linear']={**common,'kind':'linear','weights':[linear.coef_.T.tolist()],
            'biases':[linear.intercept_.tolist()], 'evaluation':{'development_action_log_loss':loss,'C':c,'train_examples':len(x)}}
        trials.extend({'kind':'linear','C':r,'development_action_log_loss':l} for l,m,r in linear_trials)
        # partial_fit consumes only training rows. No implicit random validation split.
        mlp_trials=[]
        for layers in ((32,16),(128,64)):
            model=MLPClassifier(hidden_layer_sizes=layers,activation='relu',solver='adam',alpha=.01,
                learning_rate_init=.003,random_state=seed,early_stopping=False,shuffle=True,max_iter=1)
            best=None;best_loss=math.inf;stale=0;history=[]
            for epoch in range(max_epochs):
                if time.monotonic()>deadline:
                    break
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',ConvergenceWarning)
                    model.partial_fit(tx,y,classes=np.array([0,1]))
                loss=float(log_loss(dy,model.predict_proba(dx),labels=[0,1]));history.append(loss)
                rss_peak=max(rss_peak,process.memory_info().rss)
                if loss<best_loss-1e-5:
                    best_loss=loss;best=(deepcopy(model.coefs_),deepcopy(model.intercepts_));stale=0
                else:
                    stale+=1
                if stale>=12:
                    break
            if best is None:
                raise TimeoutError('TRAINING_DEADLINE')
            mlp_trials.append((best_loss,best,layers,history))
        loss,(weights,biases),layers,history=min(mlp_trials,key=lambda item:item[0])
        bundles['mlp']={**common,'kind':'mlp','weights':[v.tolist() for v in weights],
            'biases':[v.tolist() for v in biases],'evaluation':{'development_action_log_loss':loss,
                'hidden_layers':list(layers),'early_stopping':'explicit development set; patience 12',
                'epochs':len(history),'development_loss_trace':history,'train_examples':len(x)}}
        trials.extend({'kind':'mlp','hidden_layers':list(l),'epochs':len(h),'development_action_log_loss':v} for v,b,l,h in mlp_trials)
    measurements={'training_seconds':time.perf_counter()-started,'rss_start_bytes':rss_start,
        'rss_peak_observed_bytes':rss_peak,'rss_increase_bytes':max(0,rss_peak-rss_start),'cpu_threads':1,
        'zero_logit_action_loss':float(log_loss(y,np.full(len(y),.5),labels=[0,1])),
        'trials':trials,'calibration':'unavailable; sigmoid outputs were used for fitting loss only, not exposed as confidence'}
    for kind,bundle in bundles.items():
        scorer=JsonScorer(bundle)
        samples=[]
        for _ in range(50):
            begin=time.perf_counter();scorer.logits([train_x[0]]);samples.append((time.perf_counter()-begin)*1000)
        bundle['evaluation'].update({'train_action_log_loss':float(log_loss(y,sigmoid(scorer.logits(train_x)),labels=[0,1])),
            'parameter_count':sum(np.asarray(w).size for w in bundle['weights'])+sum(len(b) for b in bundle['biases']),
            'artifact_json_bytes':len(json.dumps(bundle).encode()),
            'inference_p50_ms':float(np.quantile(samples,.5)),'inference_p95_ms':float(np.quantile(samples,.95)),
            'all_weights_zero':all(not np.any(np.asarray(w)) for w in bundle['weights'])})
        ModelBundle.model_validate(bundle)
    return bundles,measurements
