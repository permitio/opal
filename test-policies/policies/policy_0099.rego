package risk.authorization.action.allow.policy_0099

# Auto-generated policy 99 (Rego v1 syntax)
# Package: risk.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0099",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0099_allowed if {
    input.user.role == "admin"
}
policy_0099_allowed if {
    input.user.active
    input.resource.public
}
default policy_0099_allowed = false
