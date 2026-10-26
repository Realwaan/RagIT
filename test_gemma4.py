"""Explicit live provider smoke check; importing this module makes no requests."""
import argparse
import sys

from app import config as cfg, llm


def run_smoke(provider='fallback', prompt='Reply with a brief greeting.'):
    """Use one configured endpoint/model pair and surface failures without fallback."""
    if provider == 'primary':
        valid_key = llm.has_valid_primary_key()
        model, create_client = cfg.LLM_MODEL, llm.get_primary_client
    elif provider == 'fallback':
        valid_key = llm.has_valid_fallback_key()
        model, create_client = cfg.FALLBACK_MODEL, llm.get_fallback_client
    else:
        raise ValueError('Provider must be primary or fallback.')
    if not valid_key:
        raise ValueError(f'Configure a valid {provider} API key before running this live check.')

    print(f'Connecting to configured {provider} model: {model}')
    received_text = False
    with create_client() as client:
        with client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=100,
            stream=True,
        ) as stream:
            for chunk in stream:
                if chunk.choices and (text := chunk.choices[0].delta.content):
                    received_text = True
                    print(text, end='', flush=True)
    if not received_text:
        raise RuntimeError('Provider returned no text.')
    print('\n--- Stream completed ---')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__ + ' Running this script uses hosted API quota.')
    parser.add_argument('--provider', choices=('primary', 'fallback'), default='fallback')
    parser.add_argument('--prompt', default='Reply with a brief greeting.')
    args = parser.parse_args(argv)
    try:
        run_smoke(args.provider, args.prompt)
    except Exception as exc:
        # SDK exception bodies may contain request details; keep CLI errors concise.
        print(f'Live {args.provider} check failed ({type(exc).__name__}). '
              'Check the provider credentials, configured model, and endpoint.', file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
