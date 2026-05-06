package compliance.authentication.policy.check.utils.policy_0202

# Auto-generated policy 202 (Rego v1 syntax)
# Package: compliance.authentication.policy.check.utils

# Metadata
metadata := {
    "policy_id": "0202",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0202_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0202_allowed = false
policy_0202_allowed if {
    data.policies.compliance.enabled
}
