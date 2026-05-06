package access.authentication.context.allow.policy_0061

# Auto-generated policy 61 (Rego v1 syntax)
# Package: access.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0061",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0061_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0061_allowed if {
    input.user.active
    input.resource.public
}
policy_0061_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0061_allowed = false
