package security.authentication.user.allow.policy_0297

# Auto-generated policy 297 (Rego v1 syntax)
# Package: security.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0297",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0297_allowed if {
    data.policies.security.enabled
}
policy_0297_allowed if {
    input.user.active
    input.resource.public
}
policy_0297_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
