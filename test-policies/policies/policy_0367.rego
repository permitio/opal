package security.authorization.resource.check.policy_0367

# Auto-generated policy 367 (Rego v1 syntax)
# Package: security.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0367",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0367_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0367_allowed = false
policy_0367_allowed if {
    input.user.active
    input.resource.public
}
