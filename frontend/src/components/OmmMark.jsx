// OMM 로고: 요리사 모자(MM) 쓴 얼굴(O) — public/omm-mark*.png (팀 로고 이미지)
const base = import.meta.env.BASE_URL || '/'
export default function OmmMark({ size = 56, tall = false, className = '' }) {
  return tall
    ? <img className={`omm-mark ${className}`} src={`${base}omm-mark-tall.png`} alt="" aria-hidden="true" style={{ height: size, width: 'auto' }} />
    : <img className={`omm-mark ${className}`} src={`${base}omm-mark.png`} alt="" aria-hidden="true" width={size} height={size} />
}
