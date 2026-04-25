// src/hooks/usePortal.ts
import { useEffect, useRef } from 'react';

export function usePortal(id: string = 'portal-root') {
    const portalRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        // Get or create portal container
        let portalContainer = document.getElementById(id) as HTMLDivElement;

        if (!portalContainer) {
            portalContainer = document.createElement('div');
            portalContainer.id = id;
            portalContainer.style.position = 'fixed';
            portalContainer.style.top = '0';
            portalContainer.style.left = '0';
            portalContainer.style.width = '100%';
            portalContainer.style.height = '100%';
            portalContainer.style.pointerEvents = 'none';
            portalContainer.style.zIndex = '10000';
            document.body.appendChild(portalContainer);
        } else {
        }

        portalRef.current = portalContainer;

        return () => {
            // Don't remove the portal container as other citations might be using it
        };
    }, [id]);

    return portalRef.current;
}