package access.authentication.context.check.policy_0103

# Auto-generated policy 103 (Rego v1 syntax)
# Package: access.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0103",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0103_allowed = false
policy_0103_allowed if {
    input.user.active
    input.resource.public
}
policy_0103_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
