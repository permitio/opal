package access.validation.resource.check.policy_0262

# Auto-generated policy 262 (Rego v1 syntax)
# Package: access.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0262",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0262_allowed if {
    input.user.role == "admin"
}
policy_0262_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
