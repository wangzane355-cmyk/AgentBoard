/* Pure routing/summary contracts. No DOM, network, account or model calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import routing from './static/chat-routing.js';

const {resolveSend, resolveComposer, describeBatch} = routing;
const agentIds = ['codex', 'deepseek', 'reviewer', 'planner'];
const agentNames = {codex: 'Codex', deepseek: 'DeepSeek', reviewer: 'Review Agent', planner: 'Planner'};
const members = ['codex', 'deepseek'];

function resolve(overrides = {}) {
  return resolveSend({mode: 'group', agent: 'all', message: 'Review this idea', members, agentIds, agentNames, ...overrides});
}

function assertLabels(value, numbers = []) {
  for (const key of ['labelZh', 'labelEn']) {
    assert.equal(typeof value[key], 'string', key);
    assert.ok(value[key].trim(), `${key} must contain display text`);
    for (const number of numbers) {
      assert.match(value[key], new RegExp(`(^|[^0-9])${number}([^0-9]|$)`), `${key} must describe ${number}`);
    }
  }
}

function assertRoute(route, expected) {
  assert.equal(route.kind, expected.kind);
  assert.ok(!route.invalid, 'valid routes must not report an error');
  assert.equal(route.directed, expected.directed);
  assert.deepEqual(route.recipients, expected.recipients);
  assert.equal(route.rounds, expected.rounds || 1, 'ordinary one-shot sends still have one scheduling round');
  assert.equal(route.discussion_rounds, expected.rounds);
  assert.equal(route.body.discussion_rounds, expected.rounds);
  assert.equal(route.max_replies, expected.max);
  assertLabels(route, expected.rounds ? [expected.rounds, expected.max] : [expected.max]);
}

function assertInvalid(route) {
  assert.equal(route.kind, 'invalid');
  assert.ok(route.invalid, 'invalid routes must explain why they cannot be sent');
  assert.equal(route.max_replies, 0, 'an invalid draft must not advertise scheduled calls');
  assertLabels(route);
}

test('single chat schedules exactly one selected agent despite a discussion selector', () => {
  for (const selectedRounds of [undefined, 2, 3]) {
    const result = resolve({mode: 'single', agent: 'codex', selectedRounds});
    assertRoute(result, {kind: 'single', directed: true, recipients: ['codex'], rounds: 0, max: 1});
    assert.deepEqual(result.body, {message: 'Review this idea', agent: 'codex', discussion_rounds: 0});
  }
});

test('ordinary group messages default to two rounds in both preview and request', () => {
  const result = resolve();
  assertRoute(result, {kind: 'discussion', directed: false, recipients: members, rounds: 2, max: 4});
  assert.equal(result.explicitRounds, false);
  assert.deepEqual(result.body, {message: 'Review this idea', agent: 'all', discussion_rounds: 2});
});

test('the group selector controls one, two and three rounds, including DOM string values', () => {
  for (const selectedRounds of [1, 2, 3, '3']) {
    const rounds = Number(selectedRounds);
    assertRoute(resolve({selectedRounds}), {kind: 'discussion', directed: false, recipients: members, rounds, max: rounds * 2});
  }
});

test('custom group members share the six-reply ceiling without losing recipient identities', () => {
  const room = [...agentIds];
  for (const rounds of [2, 3]) {
    assertRoute(resolve({members: room, selectedRounds: rounds}), {
      kind: 'discussion', directed: false, recipients: room, rounds, max: 6,
    });
  }
});

test('choosing one recipient in a group suppresses multi-round discussion', () => {
  assertRoute(resolve({agent: 'deepseek', selectedRounds: 3}), {
    kind: 'directed', directed: true, recipients: ['deepseek'], rounds: 0, max: 1,
  });
});

for (const [command, recipient] of [['/codex', 'codex'], ['/deepseek', 'deepseek'], ['/ds', 'deepseek'], ['/reviewer', 'reviewer']]) {
  test(`${command} overrides the selected recipient and never inherits the round selector`, () => {
    const message = `${command} Check the proposal`;
    const result = resolve({agent: 'codex', selectedRounds: 3, members: agentIds, message});
    assertRoute(result, {kind: 'directed', directed: true, recipients: [recipient], rounds: 0, max: 1});
    assert.equal(result.body.message, message);
    assert.ok(result.labelZh.includes(agentNames[recipient]));
    assert.ok(result.labelEn.includes(agentNames[recipient]));
  });
}

test('custom display names remain plain strings and resolving a preview does not mutate inputs', () => {
  const name = '<img src=x onerror=alert(1)> & reviewer';
  const room = Object.freeze(['codex', 'reviewer']);
  const ids = Object.freeze(['codex', 'reviewer']);
  const names = Object.freeze({codex: 'Codex', reviewer: name});
  const input = Object.freeze({mode: 'group', agent: 'all', message: '/reviewer Review', selectedRounds: 3, members: room, agentIds: ids, agentNames: names});
  const result = resolveSend(input);
  assertRoute(result, {kind: 'directed', directed: true, recipients: ['reviewer'], rounds: 0, max: 1});
  assert.ok(result.labelZh.includes(name));
  assert.ok(result.labelEn.includes(name));
  assert.deepEqual(room, ['codex', 'reviewer']);
  assert.equal(names.reviewer, name);
});

test('/all is an explicit one-reply-per-member broadcast even when three rounds are selected', () => {
  const result = resolve({message: '/all Review once', selectedRounds: 3});
  assertRoute(result, {kind: 'broadcast', directed: false, recipients: members, rounds: 0, max: 2});
  assert.equal(result.body.discussion_rounds, 0);
});

test('a one-member room never turns ordinary, broadcast or explicit discussion messages into self replies', () => {
  for (const message of ['Review this idea', '/all Review once', '/讨论 3 Review together', '/discuss 3 Review together']) {
    const result = resolve({members:['codex'],message,selectedRounds:3});
    assertRoute(result,{kind:'broadcast',directed:false,recipients:['codex'],rounds:0,max:1});
    assert.equal(result.body.message,message);
    assert.match(result.labelZh,/仅1位成员/);
    assert.match(result.labelEn,/one member/i);
    assert.ok(result.labelZh.includes('Codex'));assert.ok(result.labelEn.includes('Codex'));
  }
});

test('running directed batches keep their accepted recipient after the input clears or a new draft is typed', () => {
  const batch=Object.freeze({user_message:'/reviewer Review this',recipients:Object.freeze(['reviewer']),directed:true,rounds:0,max_replies:1});
  for(const message of ['', 'My next question', '/all Next topic']) {
    const result=resolveComposer({mode:'group',agent:'all',message,selectedRounds:3,members:agentIds,agentIds,agentNames,running:true,batch});
    assertRoute(result,{kind:'directed',directed:true,recipients:['reviewer'],rounds:0,max:1});
    assert.match(result.labelZh,/Review Agent/);assert.match(result.labelEn,/Review Agent/);
    assert.equal(result.body.message,batch.user_message);
  }
});

test('running broadcast and discussion previews follow batch limits rather than the next selector or slash draft', () => {
  const input={mode:'group',agent:'all',message:'/reviewer Next topic',selectedRounds:3,members,agentIds,agentNames,running:true};
  const broadcast=resolveComposer({...input,batch:{user_message:'/all Review',recipients:members,directed:false,rounds:0,max_replies:2}});
  assertRoute(broadcast,{kind:'broadcast',directed:false,recipients:members,rounds:0,max:2});
  const discussion=resolveComposer({...input,batch:{user_message:'/讨论 1 Review',recipients:members,directed:false,rounds:1,max_replies:2}});
  assertRoute(discussion,{kind:'discussion',directed:false,recipients:members,rounds:1,max:2});
});

test('idle composers return to previewing the next message even when an earlier batch remains saved', () => {
  const input={mode:'group',agent:'all',message:'Next question',selectedRounds:3,members,agentIds,agentNames,running:false,
    batch:{user_message:'/reviewer Earlier question',recipients:['reviewer'],directed:true,rounds:0,max_replies:1}};
  const result=resolveComposer(input);
  assertRoute(result,{kind:'discussion',directed:false,recipients:members,rounds:3,max:6});
  assert.equal(result.body.message,'Next question');
});

for (const command of ['/讨论', '/discuss']) {
  test(`${command} with an explicit count overrides the selector`, () => {
    const message = `${command} 3 Review together`;
    const result = resolve({message, selectedRounds: 1});
    assertRoute(result, {kind: 'discussion', directed: false, recipients: members, rounds: 3, max: 6});
    assert.equal(result.explicitRounds, true);
    assert.equal(result.body.message, message);
  });

  test(`${command} without a count follows the selector and defaults to two rounds`, () => {
    for (const [selectedRounds, rounds] of [[undefined, 2], [1, 1], [3, 3]]) {
      const result = resolve({message: `${command} Review together`, selectedRounds});
      assertRoute(result, {
        kind: 'discussion', directed: false, recipients: members, rounds, max: rounds * 2,
      });
      assert.equal(result.explicitRounds, false);
    }
  });
}

test('empty rooms and unavailable directed recipients cannot schedule a send', () => {
  assertInvalid(resolve({members: []}));
  assertInvalid(resolve({members: [], message: '/all Review'}));
  assertInvalid(resolve({members: ['codex'], message: '/reviewer Review'}));
});

test('a numberless discussion command still transmits the selector when one recipient was selected', () => {
  for (const command of ['/讨论', '/discuss']) {
    for (const agent of ['all', 'codex', 'deepseek']) {
      for (const rounds of [1, 3]) {
        const route = resolve({agent, message: `${command} Review together`, selectedRounds: rounds});
        assertRoute(route, {kind:'discussion',directed:false,recipients:members,rounds,max:rounds*2});
        assert.equal(route.body.discussion_rounds, rounds, 'the backend receives a nonzero value, so its rounds-or-two fallback does not override the selector');
      }
    }
  }
});

test('unknown slash commands are rejected instead of previewing a group discussion', () => {
  assertInvalid(resolve({message: '/not-an-agent Review', selectedRounds: 3}));
});

test('single chat rejects group-only commands', () => {
  for (const message of ['/all Review', '/讨论 2 Review', '/discuss Review']) {
    assertInvalid(resolve({mode: 'single', agent: 'codex', message, selectedRounds: 3}));
  }
});

test('explicit discussion counts outside one through three are rejected', () => {
  for (const command of ['/讨论', '/discuss']) {
    for (const rounds of [0, 4, 99]) {
      assertInvalid(resolve({message: `${command} ${rounds} Review`, selectedRounds: 2}));
    }
  }
});

test('old saved batches without an end reason retain their completed-reply summary', () => {
  const summary = describeBatch({status: 'done', completed: 3, max_replies: 6});
  assertLabels(summary, [3]);
  assert.match(summary.labelZh, /批次|结束/);
  assert.match(summary.labelEn, /batch|finished|ended/i);
  assert.doesNotMatch(summary.labelZh, /共识|验证通过/);
  assert.doesNotMatch(summary.labelEn, /consensus|verified/i);
});

test('agents_done reports member declarations without claiming verified consensus', () => {
  const summary = describeBatch({status: 'done', completed: 2, end_reason: 'agents_done', completed_rounds: 1, requested_rounds: 3});
  assertLabels(summary, [2]);
  assert.match(summary.labelZh, /成员|Agent|代理/);
  assert.match(summary.labelZh, /表示|认为|声明|示意/);
  assert.match(summary.labelEn, /members|agents/i);
  assert.match(summary.labelEn, /said|indicated|signaled|declared/i);
  assert.doesNotMatch(summary.labelZh, /已达成共识|共识已验证|验证通过/);
  assert.doesNotMatch(summary.labelEn, /verified consensus|consensus verified|consensus reached|reached consensus/i);
});

const endReasons = [
  ['broadcast_complete', /每位|全体|各回复/, /each|member|once/i],
  ['directed_complete', /指定|成员|回复/, /selected|member|replied/i],
  ['round_limit', /轮/, /round/i],
  ['reply_limit', /回复|次数/, /repl|limit/i],
  ['quota_limited', /额度|配额/, /quota/i],
  ['stopped', /停止|终止/, /stop/i],
  ['deadline', /时间|超时|期限|时限/, /time|deadline/i],
  ['failed', /失败|错误/, /fail|error/i],
  ['reply_failed', /失败|错误/, /fail|error/i],
];
for (const [endReason, chinese, english] of endReasons) {
  test(`batch reason ${endReason} distinguishes the outcome and preserves the actual reply count`, () => {
    const summary = describeBatch({status: 'done', completed: 2, max_replies: 6, end_reason: endReason, completed_rounds: 1, requested_rounds: 3});
    assertLabels(summary, [2]);
    assert.match(summary.labelZh, chinese);
    assert.match(summary.labelEn, english);
  });
}

test('round-limit summaries describe actual completed and requested rounds when available', () => {
  const summary = describeBatch({status: 'done', completed: 4, end_reason: 'round_limit', completed_rounds: 2, requested_rounds: 3});
  assertLabels(summary, [4, 2, 3]);
});

test('unknown future finish reasons degrade to detail or the old reply-count summary', () => {
  for (const batch of [
    {status: 'done', completed: 1, end_reason: 'future_reason'},
    {status: 'done', completed: 1, end_reason: 'future_reason', finish_detail: 'A future scheduler ended the batch.'},
  ]) {
    const summary = describeBatch(batch);
    assertLabels(summary, [1]);
    assert.doesNotMatch(summary.labelZh, /undefined|NaN/);
    assert.doesNotMatch(summary.labelEn, /undefined|NaN/);
  }
});
