function BackgroundMain() {
  return (
    <div aria-hidden="true" style={styles.root}>
      <div style={styles.texture} />
      <div style={styles.topCurve} />
      <div style={styles.topRing} />
      <div style={styles.topGlow} />
      <div style={styles.middleBand} />
      <div style={styles.dotField} />
      <div style={styles.bottomCurve} />
      <div style={styles.bottomRing} />
      <div style={styles.rightGlow} />
      <div style={styles.dotLarge} />
      <div style={styles.dotSmall} />
    </div>
  )
}

const styles = {
  root: {
    position: 'absolute',
    inset: 0,
    overflow: 'hidden',
    pointerEvents: 'none',
    zIndex: 0,
    background:
      'linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(238, 243, 249, 1) 100%)',
  },
  texture: {
    position: 'absolute',
    inset: 0,
    opacity: 0.55,
    backgroundImage:
      'linear-gradient(135deg, rgba(31, 78, 140, 0.08) 0, rgba(31, 78, 140, 0.08) 2px, transparent 2px, transparent 34px), radial-gradient(rgba(31, 78, 140, 0.09) 1.2px, transparent 1.2px)',
    backgroundSize: '34px 34px, 24px 24px',
    backgroundPosition: '0 0, 12px 10px',
  },
  topCurve: {
    position: 'absolute',
    top: '-18%',
    left: '-8%',
    width: '88%',
    height: '48%',
    borderRadius: '50%',
    background:
      'radial-gradient(circle at center, rgba(210, 218, 228, 0.94) 0%, rgba(210, 218, 228, 0.94) 42%, rgba(210, 218, 228, 0) 73%)',
  },
  topRing: {
    position: 'absolute',
    top: '-28%',
    right: '-12%',
    width: '58%',
    height: '58%',
    borderRadius: '50%',
    border: '30px solid rgba(31, 78, 140, 0.12)',
  },
  topGlow: {
    position: 'absolute',
    top: '4%',
    right: '8%',
    width: '420px',
    height: '420px',
    borderRadius: '50%',
    background: 'radial-gradient(circle, rgba(47, 111, 178, 0.22) 0%, rgba(47, 111, 178, 0) 70%)',
    filter: 'blur(6px)',
  },
  middleBand: {
    position: 'absolute',
    top: '26%',
    left: '-10%',
    width: '70%',
    height: '22%',
    borderRadius: '999px',
    background:
      'linear-gradient(90deg, rgba(255, 255, 255, 0) 0%, rgba(244, 169, 64, 0.12) 24%, rgba(31, 78, 140, 0.12) 68%, rgba(255, 255, 255, 0) 100%)',
    transform: 'rotate(-10deg)',
  },
  dotField: {
    position: 'absolute',
    top: '14%',
    right: '5%',
    width: '26%',
    height: '34%',
    opacity: 0.9,
    backgroundImage: 'radial-gradient(rgba(31, 78, 140, 0.22) 1.6px, transparent 1.6px)',
    backgroundSize: '18px 18px',
  },
  bottomCurve: {
    position: 'absolute',
    right: '-14%',
    bottom: '-26%',
    width: '78%',
    height: '54%',
    borderRadius: '50%',
    background:
      'radial-gradient(circle at center, rgba(214, 224, 236, 0.88) 0%, rgba(214, 224, 236, 0.88) 44%, rgba(214, 224, 236, 0) 74%)',
  },
  bottomRing: {
    position: 'absolute',
    left: '-14%',
    bottom: '-28%',
    width: '44%',
    height: '44%',
    borderRadius: '50%',
    border: '22px solid rgba(244, 169, 64, 0.12)',
  },
  rightGlow: {
    position: 'absolute',
    top: '40%',
    right: '-10%',
    width: '500px',
    height: '500px',
    borderRadius: '50%',
    background: 'radial-gradient(circle, rgba(244, 169, 64, 0.2) 0%, rgba(244, 169, 64, 0) 72%)',
    filter: 'blur(8px)',
  },
  dotLarge: {
    position: 'absolute',
    right: '64px',
    top: '132px',
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    background: 'rgba(31, 78, 140, 0.18)',
  },
  dotSmall: {
    position: 'absolute',
    right: '38px',
    top: '176px',
    width: '14px',
    height: '14px',
    borderRadius: '50%',
    background: 'rgba(244, 169, 64, 0.3)',
  },
}

export default BackgroundMain
