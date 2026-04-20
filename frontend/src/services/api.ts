export async function withDelay<T>(value: T, ms = 250): Promise<T> {
  await new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })

  return value
}
