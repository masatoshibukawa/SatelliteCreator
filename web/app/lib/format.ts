export function minutes(seconds: number): string {
  return `${(seconds / 60).toFixed(1)} 分`;
}

export function kilometres(metres: number): string {
  return `${Math.round(metres / 1000)} km`;
}
