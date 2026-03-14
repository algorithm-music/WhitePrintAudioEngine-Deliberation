import { ConstraintViolation, ParameterVector, WorldState } from './types';

export function validateConstraints(
  params: ParameterVector,
  world: WorldState
): ConstraintViolation[] {
  const violations: ConstraintViolation[] = [];

  const mkt = Number(params.budget_marketing || 0);
  const rd = Number(params.budget_rd || 0);
  const ops = Number(params.budget_operations || 0);
  const sum = mkt + rd + ops;

  if (Math.abs(sum - 100) > 1) {
    violations.push({
      id: 'budget_sum',
      severity: 'high',
      message: `Total budget must sum to 100, but is ${sum}`,
      affectedParams: ['budget_marketing', 'budget_rd', 'budget_operations']
    });
  }

  const risk = Number(params.risk_level || 0.5);
  if (risk < 0 || risk > 1) {
    violations.push({
      id: 'risk_bounds',
      severity: 'fatal',
      message: `Risk level must be between 0 and 1, but is ${risk}`,
      affectedParams: ['risk_level']
    });
  }

  const timeline = Number(params.timeline_weeks || 24);
  if (timeline < 4 || timeline > 52) {
    violations.push({
      id: 'timeline_bounds',
      severity: 'fatal',
      message: `Timeline must be between 4 and 52 weeks, but is ${timeline}`,
      affectedParams: ['timeline_weeks']
    });
  }

  return violations;
}
