package audit.authorization.context.allow.policy_0031

# Auto-generated policy 31 (Rego v1 syntax)
# Package: audit.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0031",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0031_allowed if {
    input.user.role == "admin"
}
policy_0031_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0031_allowed if {
    input.user.active
    input.resource.public
}
default policy_0031_allowed = false
