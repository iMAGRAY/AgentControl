export function createCounter(initial = 0) {
  let value = initial
  return {
    inc(step = 1) {
      value += step
      return value
    },
    value() {
      return value
    }
  }
}
