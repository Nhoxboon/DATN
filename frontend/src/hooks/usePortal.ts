export function usePortal(id = 'portal-root') {
  if (typeof document === 'undefined') {
    return null
  }

  let portal = document.getElementById(id)

  if (!portal) {
    portal = document.createElement('div')
    portal.id = id
    document.body.append(portal)
  }

  return portal
}
