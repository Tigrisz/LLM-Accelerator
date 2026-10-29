"""Structured unittest result with exact test identity and no-skip acceptance."""
import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from reproduce import write_json,sha


def result_passes(result,expected):
    return (result.get('successful') is True and result.get('tests_run')==len(expected)>0 and
        result.get('skipped')==result.get('failures')==result.get('errors')==0 and
        result.get('expected_failures',0)==0 and sorted(result.get('test_ids',[]))==sorted(expected))


def flatten(suite):
    for test in suite:
        if isinstance(test,unittest.TestSuite):yield from flatten(test)
        else:yield test.id()


class Result(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.ids=[]
    def startTest(self,test):self.ids.append(test.id());super().startTest(test)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--suite',choices=('framework','tools'),required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    directory=ROOT/('tests' if args.suite=='framework' else 'tools/tests')
    suite=unittest.defaultTestLoader.discover(str(directory));discovered=sorted(flatten(suite))
    if args.suite=='framework':
        baseline=json.loads((ROOT/'tools/framework-tests-v1.json').read_text());expected=baseline['test_ids']
        if baseline.get('test_count')!=174 or len(expected)!=174 or len(set(expected))!=174 or not all(sha(ROOT/p)==h for p,h in baseline['test_source_sha256'].items()):
            raise ValueError('The fixed 174-test source/identity baseline changed; update baseline explicitly')
    else:expected=discovered
    with (args.output/'unittest.log').open('x',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(suite)
    row={'suite':args.suite,'successful':result.wasSuccessful(),'tests_run':result.testsRun,'skipped':len(result.skipped),
        'failures':len(result.failures),'errors':len(result.errors),'expected_failures':len(result.expectedFailures),
        'test_ids':result.ids,'discovered_test_ids':discovered,'expected_test_ids':expected}
    row['passed']=result_passes(row,expected) and discovered==sorted(expected)
    write_json(args.output/'result.json',row);print(json.dumps({k:row[k] for k in ('suite','passed','tests_run','skipped','failures','errors')}))
    return 0 if row['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
