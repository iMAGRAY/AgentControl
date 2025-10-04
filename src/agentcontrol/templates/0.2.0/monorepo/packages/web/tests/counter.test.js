import test from 'node:test'
import assert from 'node:assert/strict'
import { createCounter } from '../src/counter.js'

test('counter increments correctly', () => {
  const counter = createCounter()
  assert.equal(counter.inc(), 1)
  assert.equal(counter.inc(2), 3)
})
