package compliance.authorization.action.allow.core.policy_0053

# Auto-generated policy 53 (Rego v1 syntax)
# Package: compliance.authorization.action.allow.core

# Metadata
metadata := {
    "policy_id": "0053",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0053_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0053_allowed if {
    input.user.active
    input.resource.public
}
policy_0053_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
