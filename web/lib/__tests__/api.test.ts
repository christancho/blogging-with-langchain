import { parseEvent } from '../api';

describe('parseEvent', () => {
  it('routes a replay payload', () => {
    const calls: string[] = [];
    parseEvent(JSON.stringify({ replay: 'a\nb\n' }), {
      onReplay: (t) => calls.push('replay:' + t),
    });
    expect(calls).toEqual(['replay:a\nb\n']);
  });

  it('routes a line payload', () => {
    const lines: Array<[number, string]> = [];
    parseEvent(JSON.stringify({ seq: 3, line: 'hi' }), { onLine: (s, l) => lines.push([s, l]) });
    expect(lines).toEqual([[3, 'hi']]);
  });

  it('reassembles fragmented lines by seq, flushing only on the last-marked fragment', () => {
    const lines: Array<[number, string]> = [];
    const h = { onLine: (s: number, l: string) => lines.push([s, l]) };
    // Intermediate fragment is deliberately LONGER than the final one, to prove
    // reassembly does not rely on a length heuristic — only the `last` flag matters.
    parseEvent(JSON.stringify({ seq: 5, frag: 0, line: 'a'.repeat(8000) }), h);
    parseEvent(JSON.stringify({ seq: 5, frag: 1, line: 'bar', last: true }), h);
    expect(lines).toEqual([[5, 'a'.repeat(8000) + 'bar']]);
  });

  it('does not flush intermediate fragments even when short', () => {
    const lines: Array<[number, string]> = [];
    const h = { onLine: (s: number, l: string) => lines.push([s, l]) };
    // A short intermediate fragment (no `last` flag) must NOT be emitted.
    parseEvent(JSON.stringify({ seq: 7, frag: 0, line: 'x' }), h);
    expect(lines).toEqual([]);
    parseEvent(JSON.stringify({ seq: 7, frag: 1, line: 'y', last: true }), h);
    expect(lines).toEqual([[7, 'xy']]);
  });

  it('keeps fragment buffers isolated across different seqs (no leak)', () => {
    const lines: Array<[number, string]> = [];
    const h = { onLine: (s: number, l: string) => lines.push([s, l]) };
    parseEvent(JSON.stringify({ seq: 10, frag: 0, line: 'foo' }), h);
    parseEvent(JSON.stringify({ seq: 11, frag: 0, line: 'baz' }), h);
    parseEvent(JSON.stringify({ seq: 10, frag: 1, line: 'bar', last: true }), h);
    parseEvent(JSON.stringify({ seq: 11, frag: 1, line: 'qux', last: true }), h);
    expect(lines).toEqual([
      [10, 'foobar'],
      [11, 'bazqux'],
    ]);
  });

  it('routes a done event payload', () => {
    const statuses: string[] = [];
    parseEvent(JSON.stringify({ done: true, status: 'completed' }), {
      onDone: (s) => statuses.push(s),
    });
    expect(statuses).toEqual(['completed']);
  });
});
