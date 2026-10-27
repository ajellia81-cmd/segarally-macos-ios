"""Remove porting diagnostics from the pinned converter and generated shims."""
from pathlib import Path
import shutil

def _skip(text, pos):
    if text.startswith('//', pos):
        end = text.find('\n', pos + 2)
        return len(text) if end < 0 else end
    if text.startswith('/*', pos):
        end = text.find('*/', pos + 2)
        if end < 0: raise ValueError('Unterminated C comment')
        return end + 2
    if text[pos] in ('"', "'"):
        quote = text[pos]
        end = pos + 1
        while end < len(text):
            if text[end] == '\\': end += 2
            elif text[end] == quote: return end + 1
            else: end += 1
        raise ValueError('Unterminated C literal')
    return pos

def quiet_nslogs(text):
    """Remove logging arguments too; preserve control flow with a void expression."""
    pieces, copied, pos = [], 0, 0
    while pos < len(text):
        end = _skip(text, pos)
        if end != pos:
            pos = end
            continue
        if text[pos].isalpha() or text[pos] == '_':
            end = pos + 1
            while end < len(text) and (text[end].isalnum() or text[end] == '_'): end += 1
            if text[pos:end] == 'NSLog':
                begin = end
                while begin < len(text) and text[begin].isspace(): begin += 1
                if begin < len(text) and text[begin] == '(':
                    level, end = 1, begin + 1
                    while end < len(text) and level:
                        skipped = _skip(text, end)
                        if skipped != end:
                            end = skipped
                            continue
                        if text[end] == '(': level += 1
                        elif text[end] == ')': level -= 1
                        end += 1
                    if level: raise ValueError('Unterminated NSLog')
                    pieces.extend([text[copied:pos], '((void)0)'])
                    copied = end
            pos = end
        else:
            pos += 1
    pieces.append(text[copied:])
    return ''.join(pieces)

def _once(text, old, new):
    if text.count(old) != 1: raise ValueError('Pinned converter section changed: ' + old[:60])
    return text.replace(old,new)

def prepare_release(root):
    overrides = root / 'shim/overrides'
    (overrides / 'AppKit_Stats.m').unlink()
    (overrides / 'Port0rLog.h').unlink(missing_ok=True)

    runtime = overrides / 'AppKit_RuntimeHooks.m'
    text = runtime.read_text()
    start = text.index('// MARK: method tracing')
    text = text[:start]  # tracing, pacing diagnostics and GC diagnostic-only swizzles
    start = text.index('    static int ok;')
    end = text.index('    if (error) *error = e;', start)
    text = text[:start] + text[end:]  # remove shader dump files, preserve metallib retry/errors
    start = text.index('    static NSMutableSet *seen;', text.index('- (void)forwardInvocation:'))
    end = text.index('    uint64_t zero = 0;', start)
    text = text[:start] + text[end:]  # preserve the compatibility sink, remove diagnostic history
    runtime.write_text(text)

    appkit = overrides / 'AppKit.m'
    text = appkit.read_text()
    start = text.index('    static unsigned polls, delivered; static CFAbsoluteTime last;')
    end = text.index('    return e;', start)
    text = text[:start] + text[end:]
    start = text.index('        // Metal HUD follows one layer;')
    # Objective-C dictionary literals contain @-prefixed strings.
    end = text.index('developerHUDProperties = @{@' + '"mode": @' + '"default"};',start)
    end = text.index(';',end) + 1
    text = text[:start] + text[end:]
    appkit.write_text(text)

    libc = overrides / 'libSystem.m'
    text = libc.read_text()
    start = text.index('static void LogMissing(')
    end = text.index('#define EXPORT',start)
    text = text[:start] + text[end:]
    for call in ['open','stat','access']:
        text = _once(text, 'LogMissing("' + call + '", path, r); ', '')
    start = text.index('// MARK: Crash handlers')
    signal = text[text.index('EXPORT void (*signal(',start):]
    text = text[:start] + '''// Preserve native signal APIs without diagnostic interposition.
EXPORT int sigaction(int sig, const struct sigaction *act, struct sigaction *old) {
    REAL(int, "sigaction", int, const struct sigaction *, struct sigaction *);
    return real(sig, act, old);
}

''' + signal
    libc.write_text(text)

    for source in overrides.glob('*.m'):
        source.write_text(quiet_nslogs(source.read_text()))

    # Apply the same quiet generation to automatically produced missing-API stubs.
    converter = root / 'tools/convert_app.py'
    text = converter.read_text()
    text = _once(text, 'def main():\n', 'def main():\n    from port0r_release import quiet_nslogs\n')
    text = _once(text, 'open(src, "w").write(gen_stub_source(', 'open(src, "w").write(quiet_nslogs(gen_stub_source(')
    text = _once(text, '                                             hand[p][0]))',
                       '                                             hand[p][0])))')
    text = _once(text, 'cmd = ["xcrun", "-sdk", "iphoneos", "clang", "-fobjc-arc", "-target"',
                       'cmd = ["xcrun", "-sdk", "iphoneos", "clang", "-fobjc-arc", "-Os", "-target"')
    converter.write_text(text)
    shutil.copyfile(Path(__file__), root / 'tools/port0r_release.py')
