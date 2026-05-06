package compliance.authorization.action.check.policy_0613

# Auto-generated policy 613 (Rego v1 syntax)
# Package: compliance.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0613",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0613_allowed = false
policy_0613_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
