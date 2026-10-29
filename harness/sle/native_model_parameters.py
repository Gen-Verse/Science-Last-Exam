"""Explicit, recorded generation parameters for native Claude Code gateways."""
import json
import math

FIELDS = {'temperature', 'top_p', 'thinking', 'output_config', 'max_tokens'}


def validate_model_parameters(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('model_parameters must explicitly contain temperature, top_p, thinking, output_config and max_tokens')
    result = json.loads(json.dumps(value, allow_nan=False))
    for key, upper in [('temperature', 2), ('top_p', 1)]:
        number = result[key]
        if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= upper:
            raise ValueError(f'Invalid explicit {key}')
    if type(result['max_tokens']) is not int or result['max_tokens'] < 1:
        raise ValueError('max_tokens must be a positive integer')
    thinking = result['thinking']
    if not isinstance(thinking, dict) or thinking.get('type') not in {'enabled', 'disabled', 'adaptive'}:
        raise ValueError('thinking.type must be explicit')
    if set(thinking) - {'type', 'budget_tokens'}:
        raise ValueError('Unsupported thinking parameter')
    if 'budget_tokens' in thinking:
        budget = thinking['budget_tokens']
        if type(budget) is not int or not 0 < budget < result['max_tokens']:
            raise ValueError('thinking.budget_tokens must be positive and below max_tokens')
    output = result['output_config']
    if not isinstance(output, dict) or set(output) != {'effort'} or output['effort'] not in {'low', 'medium', 'high', 'xhigh', 'max', 'ultracode'}:
        raise ValueError('output_config.effort must be explicit')
    return result


def model_parameter_environment(parameters):
    if parameters is None:
        # Historical direct agent configs remain loadable. Launchers require
        # a complete profile for every newly generated benchmark trial.
        return {}
    parameters = validate_model_parameters(parameters)
    return {'CLAUDE_CODE_MAX_OUTPUT_TOKENS': str(parameters['max_tokens']),
            'CLAUDE_CODE_EFFORT_LEVEL': parameters['output_config']['effort'],
            'CLAUDE_CODE_EXTRA_BODY': json.dumps(parameters, separators=(',', ':'))}
