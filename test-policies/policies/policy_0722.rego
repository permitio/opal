package security.enforcement.resource.validate.policy_0722

# Auto-generated policy 722 (Rego v1 syntax)
# Package: security.enforcement.resource.validate

# Metadata
metadata := {
    "policy_id": "0722",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0722_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0722_allowed = false
