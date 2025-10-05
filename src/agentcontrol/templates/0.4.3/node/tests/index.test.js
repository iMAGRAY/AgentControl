import test from 'node:test'
import assert from 'node:assert/strict'
import { greet } from '../src/index.js'

test('greet returns default message', () => {
  assert.equal(greet(), 'Hello, AgentControl!')
})
