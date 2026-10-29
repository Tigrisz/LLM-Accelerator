"""T4 profile parameters: one source for actual -G arguments and report records."""
import re
from rv32_evidence import classify_simulation

_COMMON={'RAM_WORDS':16384,'SIM_FAST_UART':1,'CLOCK_HZ':27000000,'PREDICT_ENABLE':1,
         'BTB_BITS':8,'LOAD_BYPASS':1,'EARLY_LSU':1,'INIT_FILE':'firmware.hex'}
_DUAL={'single_issue':0,'dual_issue':1}
_BITS={'DUAL_ISSUE','SIM_FAST_UART','PREDICT_ENABLE','LOAD_BYPASS','EARLY_LSU'}


def parameters(profile):
    if profile not in _DUAL:raise ValueError('Unknown RTL profile')
    return {'DUAL_ISSUE':_DUAL[profile],**_COMMON}


def verilator_arguments(values):
    if set(values)!=set(_COMMON)|{'DUAL_ISSUE'}:raise ValueError('Incomplete/unknown RTL parameters')
    result=[]
    for name,value in values.items():
        if name=='INIT_FILE':
            if value!='firmware.hex':raise ValueError('Unexpected initialization image name')
            result.append(f'-G{name}="{value}"')
        elif type(value) is not int or value<0 or name in _BITS and value not in (0,1):
            raise ValueError('Invalid RTL parameter value')
        else:result.append(f"-G{name}=1'b{value}" if name in _BITS else f'-G{name}={value}')
    return result


def check_build_parameters(command,values):
    expected=verilator_arguments(values)
    actual=[str(arg) for arg in command if str(arg).startswith('-G')]
    if len(actual)!=len(expected) or set(actual)!=set(expected):raise ValueError('Reported RTL parameters differ from actual build arguments')
    return True


def profile_record(profile,command,elf_sha256,result,validation,wrong_result,wrong_validation,watch_result,watch_validation,rtl_sha256):
    values=parameters(profile);check_build_parameters(command,values)
    if not all(isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) for value in (elf_sha256,rtl_sha256)):
        raise ValueError('ELF/RTL identity required for each profile')
    if not isinstance(validation,dict) or 'passed' not in validation or validation['passed'] is not None and type(validation['passed']) is not bool:
        raise ValueError('Profile simulation status must be true/false/null')
    def control(observed,checked):
        if (observed is None)!=(checked is None):raise ValueError('Negative-control result/validation availability differs')
        return {'tested':observed is not None,'result':observed,'validation':checked}
    return {'parameters':values,'build_command':list(map(str,command)),'normal_elf_sha256':elf_sha256,'rtl_sha256':rtl_sha256,
        'normal':{'result':result,'validation':validation},'simulation_passed':validation['passed'],
        'negative_controls':{'wrong_expected':control(wrong_result,wrong_validation),'watchdog':control(watch_result,watch_validation)},
        'scope':'selected RTL simulation only; no board or worst-case stack conclusion',
        'board_verified':False,'formal_equivalence':None,'full_stack_worst_case':None}


def complete_dual_validation(result,normal_expected,zero_expected):
    validation=classify_simulation(result,normal_expected)
    if validation['passed'] is not True:return validation
    fields=result.get('fields',{})
    checks=[(result.get('zero_values'),zero_expected),
        *[(fields.get(key),expected) for key,expected in [('NEGATIVE_CHECKS',3),('SYNC_PUBLISH',2),('SYNC_ACQUIRE',2)]]]
    if all(actual==expected for actual,expected in checks):return validation
    confirmed=any(actual is not None and actual!=expected for actual,expected in checks)
    return {'passed':False if confirmed else None,'failure_confirmed':confirmed,'state':'failed' if confirmed else 'unproven',
        'reason':'Zero-input/fault/synchronization result differs or is incomplete','root_cause':None}


class ProfileValidationError(ValueError):
    def __init__(self,profiles):
        profile=profiles['dual_issue']
        super().__init__('Portable RTL dual-issue positive validation failed/incomplete; formed evidence retained')
        self.evidence={'target_result':profile['simulation_passed'],'failure_profile':'dual_issue',
            'rtl_profiles_version':1,'rtl_profiles':profiles,'classification':profile['normal']['validation'],
            'scope':'selected RTL positive simulation; subsequent dual negative controls not executed'}


def require_dual_pass(profiles):
    if profiles['dual_issue']['simulation_passed'] is not True:raise ProfileValidationError(profiles)
