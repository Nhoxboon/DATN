// src/hooks/usePopupPosition.ts
import { useEffect, useState, RefObject } from 'react';

interface PopupPosition {
    left: number;
    top: number;
    placement: 'above' | 'below';
    arrow: { left: number };
}

interface UsePopupPositionProps {
    isVisible: boolean;
    triggerRef: RefObject<HTMLElement>;
    popupRef: RefObject<HTMLElement>;
    offset?: number;
    padding?: number;
}

export function usePopupPosition({
    isVisible,
    triggerRef,
    popupRef,
    offset = 12,
    padding = 20,
}: UsePopupPositionProps) {
    const [position, setPosition] = useState<PopupPosition>({
        left: 0,
        top: 0,
        placement: 'above',
        arrow: { left: 0 },
    });

    useEffect(() => {
        if (!isVisible || !triggerRef.current || !popupRef.current) {
            return;
        }

        const calculatePosition = () => {
            if (!triggerRef.current || !popupRef.current) return;

            const triggerRect = triggerRef.current.getBoundingClientRect();
            const popupRect = popupRef.current.getBoundingClientRect();
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;

            // Calculate available space
            const spaceAbove = triggerRect.top;
            const spaceBelow = viewportHeight - triggerRect.bottom;

            // Determine vertical placement
            let placement: 'above' | 'below' = 'above';
            let top = 0;

            const popupHeight = popupRect.height || 400; // Use actual or max height

            if (spaceAbove >= popupHeight + offset) {
                // Enough space above
                placement = 'above';
                top = triggerRect.top - popupHeight - offset;
            } else if (spaceBelow >= popupHeight + offset) {
                // Not enough space above, try below
                placement = 'below';
                top = triggerRect.bottom + offset;
            } else {
                // Not enough space in either direction
                // Choose the side with more space
                if (spaceAbove > spaceBelow) {
                    placement = 'above';
                    // Calculate ideal position above the trigger
                    const idealTop = triggerRect.top - popupHeight - offset;
                    const minTop = padding;

                    // If ideal position would be above viewport, clamp it
                    top = Math.max(minTop, idealTop);

                    // CRITICAL FIX: Check if popup would overlap the trigger after clamping
                    const popupBottom = top + popupHeight;
                    const wouldOverlap = popupBottom > triggerRect.top - offset;

                    if (wouldOverlap) {
                        // Not enough space above without overlap - switch to below instead
                        placement = 'below';
                        top = triggerRect.bottom + offset;
                        const maxTop = viewportHeight - popupHeight - padding;
                        top = Math.min(top, maxTop);

                        // Ensure it's always below the trigger
                        const minTopBelowTrigger = triggerRect.bottom + offset;
                        top = Math.max(top, minTopBelowTrigger);

                    } else {
                    }
                } else {
                    placement = 'below';
                    // Place below the trigger with offset
                    top = triggerRect.bottom + offset;
                    const maxTop = viewportHeight - popupHeight - padding;

                    // Ensure popup doesn't go off bottom of screen
                    top = Math.min(top, maxTop);

                    // CRITICAL FIX: Ensure popup is always BELOW the trigger, never overlaps it
                    const minTopBelowTrigger = triggerRect.bottom + offset;
                    top = Math.max(top, minTopBelowTrigger);
                }
            }

            // Calculate horizontal position (centered on trigger)
            const popupWidth = popupRect.width || 480;
            let left = triggerRect.left + (triggerRect.width / 2) - (popupWidth / 2);

            // Keep within viewport bounds
            const minLeft = padding;
            const maxLeft = viewportWidth - popupWidth - padding;
            left = Math.max(minLeft, Math.min(left, maxLeft));

            // Calculate arrow position (relative to popup)
            const triggerCenter = triggerRect.left + (triggerRect.width / 2);
            const arrowLeft = triggerCenter - left;

            const finalPosition = {
                left,
                top,
                placement,
                arrow: { left: arrowLeft },
            };
            setPosition(finalPosition);
        };

        // Calculate initially
        calculatePosition();

        // Recalculate on scroll or resize
        const handleUpdate = () => {
            calculatePosition();
        };

        window.addEventListener('scroll', handleUpdate, true);
        window.addEventListener('resize', handleUpdate);

        return () => {
            window.removeEventListener('scroll', handleUpdate, true);
            window.removeEventListener('resize', handleUpdate);
        };
    }, [isVisible, offset, padding]);

    return position;
}