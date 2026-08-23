export async function getMe() {
  const response = await fetch('/api/me')
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }
  return response.json()
}
