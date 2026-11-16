import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseWebhookBody, verifyWebhookToken } from '../../src/core/triggers/webhook.ts'

test('verifyWebhookToken: accepts the matching bearer token', () => {
  assert.equal(
    verifyWebhookToken({ authorization: 'Bearer s3cret' }, 's3cret'),
    true,
  )
  // Header names are case-insensitive.
  assert.equal(
    verifyWebhookToken({ Authorization: 'Bearer s3cret' }, 's3cret'),
    true,
  )
  // The scheme is case-insensitive per RFC 7235.
  assert.equal(
    verifyWebhookToken({ authorization: 'bearer s3cret' }, 's3cret'),
    true,
  )
})

test('verifyWebhookToken: rejects wrong, missing, or malformed tokens', () => {
  assert.equal(verifyWebhookToken({ authorization: 'Bearer wrong' }, 's3cret'), false)
  assert.equal(verifyWebhookToken({}, 's3cret'), false)
  assert.equal(verifyWebhookToken({ authorization: undefined }, 's3cret'), false)
  assert.equal(verifyWebhookToken({ authorization: 'Basic s3cret' }, 's3cret'), false)
  assert.equal(verifyWebhookToken({ authorization: 'Bearer' }, 's3cret'), false)
  // An empty expected token never verifies.
  assert.equal(verifyWebhookToken({ authorization: 'Bearer ' }, ''), false)
})

test('verifyWebhookToken: multi-value headers match any value', () => {
  assert.equal(
    verifyWebhookToken({ authorization: ['Bearer wrong', 'Bearer s3cret'] }, 's3cret'),
    true,
  )
  assert.equal(
    verifyWebhookToken({ authorization: ['Bearer a', 'Bearer b'] }, 's3cret'),
    false,
  )
})

test('verifyWebhookToken: exact token comparison, not prefix', () => {
  assert.equal(verifyWebhookToken({ authorization: 'Bearer s3cret-extra' }, 's3cret'), false)
  assert.equal(verifyWebhookToken({ authorization: 'Bearer s3' }, 's3cret'), false)
})

test('parseWebhookBody: returns the JSON value or null', () => {
  assert.deepEqual(parseWebhookBody('{"a":1}'), { a: 1 })
  assert.deepEqual(parseWebhookBody('[1,2]'), [1, 2])
  assert.equal(parseWebhookBody('42'), 42)
  assert.equal(parseWebhookBody('null'), null)
  assert.equal(parseWebhookBody('not json'), null)
  assert.equal(parseWebhookBody(''), null)
  assert.equal(parseWebhookBody('{broken'), null)
})
