// Uses the app's real Supabase client in manually authenticated browser sessions.
// Writes only new, explicitly named isolation-fixture workspaces; never customer rows.
import { mkdir, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';

export async function reviewWorkspaceIsolation(sessions) {
  const run = `isolation-${randomUUID()}`;
  const evidence = { run, status: 'NOT TESTED', fixtures: [], checks: [] };
  await mkdir('.ui-review/isolation', { recursive: true });
  const save = () => writeFile(`.ui-review/isolation/${run}.json`, JSON.stringify(evidence, null, 2));
  const identities = [];
  for (const { page } of sessions) {
    identities.push(await page.evaluate(async () => {
      const { supabase } = await import('/src/lib/supabase/client.ts');
      const { data, error } = await supabase.auth.getUser();
      if (error || !data.user) throw new Error('Manual sign-in required');
      return data.user.id;
    }));
  }
  if (identities[0] === identities[1]) throw new Error('Two different accounts are required');
  for (const { label, page } of sessions) {
    const result = await page.evaluate(async ({ name }) => {
      const { dashboardService } = await import('/src/services/dashboardService.ts');
      try {
        const row = await dashboardService.createWorkspace(name, 'Dedicated authorization acceptance fixture');
        return row ? { id: row.id, created: true } : { created: false, error: 'No workspace returned' };
      } catch (error) { return { created: false, error: error.message }; }
    }, { name: `${run}-${label}` });
    evidence.fixtures.push({ account: label, ...result });
    await save();
    if (!result.created) {
      evidence.status = 'BLOCKED';
      await save();
      return evidence;
    }
  }
  for (let i = 0; i < sessions.length; i++) {
    const own = evidence.fixtures[i].id;
    const other = evidence.fixtures[1 - i].id;
    const result = await sessions[i].page.evaluate(async ({ own, other, run }) => {
      const { supabase } = await import('/src/lib/supabase/client.ts');
      const owned = await supabase.from('workspaces').select('id').eq('id', own);
      const foreign = await supabase.from('workspaces').select('id').eq('id', other);
      const mutation = await supabase.from('workspaces').update({ description: `${run}-unauthorized` }).eq('id', other).select('id');
      return {
        ownRead: !owned.error && owned.data?.length === 1,
        crossReadDenied: !foreign.error && foreign.data?.length === 0,
        crossUpdateDenied: Boolean(mutation.error) || mutation.data?.length === 0,
        errors: [owned.error?.code, foreign.error?.code, mutation.error?.code].filter(Boolean),
      };
    }, { own, other, run });
    evidence.checks.push({ account: sessions[i].label, ...result });
    await save();
  }
  evidence.status = evidence.checks.every(c => c.ownRead && c.crossReadDenied && c.crossUpdateDenied) ? 'PASS' : 'FAIL';
  // Fixtures are retained for inspection/repeat verification; no broad cleanup.
  await save();
  return evidence;
}
