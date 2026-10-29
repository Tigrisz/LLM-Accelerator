"""Evidence gates for T2; independent of target compilers and hardware."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from check_target_platform import audit


class TargetEvidenceTests(unittest.TestCase):
    def copy_evidence(self,directory):
        root=Path(directory)
        shutil.copytree(ROOT/'docs/target_platform_sources',root/'docs/target_platform_sources')
        shutil.copy2(ROOT/'docs/target_platform_constraints.json',root/'docs/target_platform_constraints.json')
        manifest=json.loads((root/'docs/target_platform_sources/manifest.json').read_text(encoding='utf-8'))
        for row in manifest['sources']:
            p=root/row['path']
            if not p.exists():
                p.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/row['path'],p)
        return root

    def rewrite(self,root,change):
        p=root/'docs/target_platform_constraints.json'
        data=json.loads(p.read_text(encoding='utf-8'));change(data)
        p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')

    def test_actual_evidence_and_unknowns(self):
        report=audit(ROOT)
        self.assertEqual(report['constraint_count'],54)
        self.assertEqual(report['statuses']['unknown'],13)
        self.assertFalse(report['target_execution_verified'])
        self.assertTrue(all(v is None for v in report['target_budgets'].values()))

    def test_source_corruption_and_locator_change_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.copy_evidence(directory)
            p=root/'docs/target_platform_sources/main/sw/link.ld'
            p.write_bytes(p.read_bytes()+b'\n// altered')
            with self.assertRaises(ValueError):audit(root)
        with tempfile.TemporaryDirectory() as directory:
            root=self.copy_evidence(directory)
            self.rewrite(root,lambda d:d['constraints'][0]['evidence'][0].update(line=1))
            with self.assertRaises(ValueError):audit(root)

    def test_unknown_pc_budget_and_readiness_rejected(self):
        mutations=[lambda d:d['target_budgets'].update(arena_bytes=64*1024*1024),
                   lambda d:d.update(target_ready=True),
                   lambda d:d.update(quantization='W4A8'),
                   lambda d:next(x for x in d['constraints'] if x['status']=='unknown').update(value='assume GCC')]
        for change in mutations:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                root=self.copy_evidence(directory);self.rewrite(root,change)
                with self.assertRaises(ValueError):audit(root)

    def test_missing_required_item_and_false_status_rejected(self):
        mutations=[lambda d:d['constraints'].remove(next(x for x in d['constraints'] if x['id']=='memory.arena_budget')),
                   lambda d:next(x for x in d['constraints'] if x['id']=='toolchain.current').update(status='source_confirmed')]
        for change in mutations:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                root=self.copy_evidence(directory);self.rewrite(root,change)
                with self.assertRaises(ValueError):audit(root)

    def test_resource_value_without_evidence_change_rejected(self):
        mutations=[lambda d:next(x for x in d['constraints'] if x['id']=='memory.tcm')['value'].update(bytes=64*1024*1024),
                   lambda d:next(x for x in d['constraints'] if x['id']=='stack.inspect_scratch').update(value=4096)]
        for change in mutations:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                root=self.copy_evidence(directory);self.rewrite(root,change)
                with self.assertRaises(ValueError):audit(root)

    def test_source_set_blob_and_commit_identity_rejected(self):
        for mutation in ('omit_sources','omit_blob_fields','target_commit','index_commit','source_ref','repository_path'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as directory:
                root=self.copy_evidence(directory)
                p=root/'docs/target_platform_sources/manifest.json'
                manifest=json.loads(p.read_text(encoding='utf-8'))
                if mutation=='omit_sources':
                    manifest['sources']=[s for s in manifest['sources'] if s['id']!='repository_index']
                elif mutation=='omit_blob_fields':
                    for s in manifest['sources']:s.pop('git_blob_sha1',None)
                elif mutation=='target_commit':
                    self.rewrite(root,lambda d:d.update(target_commit='0'*40))
                elif mutation=='index_commit':
                    index=root/'docs/target_platform_sources/repository.json'
                    data=json.loads(index.read_text(encoding='utf-8'));data['ref']='0'*40
                    index.write_text(json.dumps(data),encoding='utf-8')
                    # Bypass the hash-only gate to exercise cross-index identity.
                    import hashlib
                    next(s for s in manifest['sources'] if s['id']=='repository_index')['sha256']=hashlib.sha256(index.read_bytes()).hexdigest()
                elif mutation=='source_ref':manifest['sources'][0]['ref']='0'*40
                else:manifest['sources'][0]['path']='docs/target_platform_sources/main/sw/link.ld'
                p.write_text(json.dumps(manifest),encoding='utf-8')
                with self.assertRaises(ValueError):audit(root)


if __name__=='__main__':unittest.main()
