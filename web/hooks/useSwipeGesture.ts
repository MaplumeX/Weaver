import { useEffect, useRef } from 'react'

interface SwipeConfig {
    onSwipeLeft?: () => void
    onSwipeRight?: () => void
    threshold?: number
}

export function useSwipeGesture(
    ref: React.RefObject<HTMLElement>,
    { onSwipeLeft, onSwipeRight, threshold = 50 }: SwipeConfig
) {
    const touchStart = useRef<number | null>(null)
    const touchEnd = useRef<number | null>(null)

    useEffect(() => {
        const element = ref.current
        if (!element) return

        const handleTouchStart = (e: TouchEvent) => {
            touchEnd.current = null
            const firstTouch = e.targetTouches.item(0)
            if (!firstTouch) return
            touchStart.current = firstTouch.clientX
        }

        const handleTouchMove = (e: TouchEvent) => {
            const firstTouch = e.targetTouches.item(0)
            if (!firstTouch) return
            touchEnd.current = firstTouch.clientX
        }

        const handleTouchEnd = () => {
            if (!touchStart.current || !touchEnd.current) return

            const distance = touchStart.current - touchEnd.current
            const isLeftSwipe = distance > threshold
            const isRightSwipe = distance < -threshold

            if (isLeftSwipe && onSwipeLeft) {
                onSwipeLeft()
            }

            if (isRightSwipe && onSwipeRight) {
                onSwipeRight()
            }
        }

        element.addEventListener('touchstart', handleTouchStart, { passive: true })
        element.addEventListener('touchmove', handleTouchMove, { passive: true })
        element.addEventListener('touchend', handleTouchEnd)

        return () => {
            element.removeEventListener('touchstart', handleTouchStart)
            element.removeEventListener('touchmove', handleTouchMove)
            element.removeEventListener('touchend', handleTouchEnd)
        }
    }, [ref, onSwipeLeft, onSwipeRight, threshold])
}
