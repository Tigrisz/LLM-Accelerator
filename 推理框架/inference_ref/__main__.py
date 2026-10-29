"""Model-independent fixture, C backend and model package tools."""

import argparse
import json
from pathlib import Path
import sys

from .contracts import ContractError, require
from .reporting import write_json_exclusive
from .suite import generate_suite, verify_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-1A model-independent reference tools")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Create a new synthetic fixture suite")
    generate.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="Check stored, scalar and NumPy results")
    verify.add_argument("--fixtures", type=Path, required=True)
    verify.add_argument("--report", type=Path, required=True)
    verify_c = commands.add_parser("verify-c", help="Build and validate the PC C backend")
    verify_c.add_argument("--fixtures", type=Path, required=True)
    verify_c.add_argument("--output", type=Path, required=True)
    verify_c.add_argument("--cc", help="C compiler executable (not a shell command)")
    inspect = commands.add_parser("inspect-model", help="Validate package and display static memory plan")
    inspect.add_argument("--package", type=Path, required=True)
    inspect.add_argument("--memory-budget", type=int, default=64*1024*1024)
    packages = commands.add_parser("verify-packages", help="Package fixtures and validate planned C sessions")
    packages.add_argument("--fixtures", type=Path, required=True)
    packages.add_argument("--output", type=Path, required=True)
    packages.add_argument("--cc", help="C compiler executable (not a shell command)")
    device = commands.add_parser("verify-device", help="Validate simulated task lifecycle and C model execution")
    device.add_argument("--fixtures", type=Path, required=True)
    device.add_argument("--output", type=Path, required=True)
    device.add_argument("--cc", help="C compiler executable (not a shell command)")
    trace = commands.add_parser("verify-trace", help="Validate runtime tracing and export correlated timeline")
    trace.add_argument("--fixtures", type=Path, required=True)
    trace.add_argument("--output", type=Path, required=True)
    trace.add_argument("--cc", help="C compiler executable (not a shell command)")
    backends=commands.add_parser('verify-backends',help='Validate whole-chain backend selection and explicit fallback')
    backends.add_argument('--fixtures',type=Path,required=True)
    backends.add_argument('--output',type=Path,required=True)
    backends.add_argument('--cc',help='C compiler executable (not a shell command)')
    platform=commands.add_parser('verify-platform',help='Validate PC platform reads, memory, clock and synchronization')
    platform.add_argument('--fixtures',type=Path,required=True)
    platform.add_argument('--output',type=Path,required=True)
    platform.add_argument('--cc',help='C compiler executable (not a shell command)')
    static=commands.add_parser('verify-static',help='Validate offline export and standalone pure C runtime')
    static.add_argument('--fixtures',type=Path,required=True)
    static.add_argument('--output',type=Path,required=True)
    static.add_argument('--cc')
    export=commands.add_parser('export-static',help='Check and plan a package offline, export pointer-free execution image')
    export.add_argument('--package',type=Path,required=True)
    export.add_argument('--output',type=Path,required=True)
    export.add_argument('--address-bits',type=int,choices=(32,64),default=64)
    export.add_argument('--memory-budget',type=int,default=64*1024*1024)
    resources=commands.add_parser('verify-resources',help='Validate runtime resource ledger and pressure recovery')
    resources.add_argument('--fixtures',type=Path,required=True)
    resources.add_argument('--output',type=Path,required=True)
    resources.add_argument('--cc')
    resources.add_argument('--iterations',type=int,default=200)
    args = parser.parse_args()
    try:
        if args.command=='verify-resources':
            from .resource_validation import run_resource_validation
            result=run_resource_validation(args.fixtures,args.output,args.cc,iterations=args.iterations)
            print(json.dumps({'passed':result['passed'],'case_count':result['case_count'],'passed_count':result['passed_count'],
                'report':str(args.output.resolve()/'report.json')},ensure_ascii=False))
            return 0 if result['passed'] else 1
        if args.command=='export-static':
            from .static_export import export_static
            print(json.dumps(export_static(args.package,args.output,address_bits=args.address_bits,memory_budget=args.memory_budget),ensure_ascii=False))
            return 0
        if args.command=='verify-static':
            from .static_validation import run_static_validation
            result=run_static_validation(args.fixtures,args.output,args.cc)
            print(json.dumps({'passed':result['passed'],'case_count':result['case_count'],'passed_count':result['passed_count'],
                'report':str(args.output.resolve()/'report.json')},ensure_ascii=False))
            return 0 if result['passed'] else 1
        if args.command == "generate":
            result = generate_suite(args.output)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command=='verify-backends':
            from .backend_validation import run_backend_validation
            result=run_backend_validation(args.fixtures,args.output,args.cc)
            print(json.dumps({'passed':result['passed'],'case_count':result['case_count'],'passed_count':result['passed_count'],
                              'report':str(args.output.resolve()/'report.json')},ensure_ascii=False))
            return 0 if result['passed'] else 1
        if args.command=='verify-platform':
            from .platform_validation import run_platform_validation
            result=run_platform_validation(args.fixtures,args.output,args.cc)
            print(json.dumps({'passed':result['passed'],'case_count':result['case_count'],'passed_count':result['passed_count'],
                              'report':str(args.output.resolve()/'report.json')},ensure_ascii=False))
            return 0 if result['passed'] else 1
        if args.command == "inspect-model":
            from .runtime import inspect_model
            print(json.dumps(inspect_model(args.package, memory_budget=args.memory_budget), ensure_ascii=False))
            return 0
        if args.command == "verify-device":
            from .device_validation import run_device_validation
            result = run_device_validation(args.fixtures, args.output, args.cc)
            print(json.dumps({"passed": result["passed"], "case_count": result["case_count"],
                              "passed_count": result["passed_count"],
                              "report": str(args.output.resolve() / "report.json")}, ensure_ascii=False))
            return 0 if result["passed"] else 1
        if args.command == "verify-trace":
            from .trace_validation import run_trace_validation
            result = run_trace_validation(args.fixtures,args.output,args.cc)
            print(json.dumps({"passed":result["passed"],"case_count":result["case_count"],
                              "passed_count":result["passed_count"],"report":str(args.output.resolve()/"report.json")},ensure_ascii=False))
            return 0 if result["passed"] else 1
        if args.command == "verify-packages":
            from .package_validation import run_package_validation
            result = run_package_validation(args.fixtures, args.output, args.cc)
            print(json.dumps({"passed": result["passed"], "case_count": result["case_count"],
                              "passed_count": result["passed_count"],
                              "report": str(args.output.resolve() / "report.json")}, ensure_ascii=False))
            return 0 if result["passed"] else 1
        if args.command == "verify-c":
            from .c_backend import run_validation
            result = run_validation(args.fixtures, args.output, args.cc)
            print(json.dumps({"passed": result["passed"], "case_count": result["case_count"],
                              "passed_count": result["passed_count"],
                              "report": str(args.output.resolve() / "report.json")},
                             ensure_ascii=False))
            return 0 if result["passed"] else 1
        root, report_path = args.fixtures.resolve(), args.report.resolve()
        require(not report_path.is_relative_to(root), "INVALID_ARGUMENT",
                "Report must be outside the input suite")
        result = verify_suite(root)
        write_json_exclusive(report_path, result)
        print(json.dumps({"passed": result["passed"], "case_count": result["case_count"],
                          "passed_count": result["passed_count"],
                          "report": str(report_path)}, ensure_ascii=False))
        return 0 if result["passed"] else 1
    except ContractError as exc:
        print(json.dumps({"error": exc.code, "message": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
