package audit.authentication.policy.check.policy_0991

# Auto-generated policy 991 (Rego v1 syntax)
# Package: audit.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0991",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0991_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0991_allowed if {
    input.user.active
    input.resource.public
}
default policy_0991_allowed = false
