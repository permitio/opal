package governance.authorization.context.allow.utils.policy_0758

# Auto-generated policy 758 (Rego v1 syntax)
# Package: governance.authorization.context.allow.utils

# Metadata
metadata := {
    "policy_id": "0758",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0758_allowed = false
policy_0758_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0758_allowed if {
    input.user.active
    input.resource.public
}
policy_0758_allowed if {
    input.user.role == "admin"
}
