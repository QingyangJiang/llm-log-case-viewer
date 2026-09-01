export const BADCASE_AUTO_SCORE_THRESHOLD = 8;

export function shouldAutoMarkBadcase(score: number) {
  return Number.isFinite(score) && score < BADCASE_AUTO_SCORE_THRESHOLD;
}
