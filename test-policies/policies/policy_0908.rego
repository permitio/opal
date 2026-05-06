package access.validation.user.deny.policy_0908

# Auto-generated policy 908 (Rego v1 syntax)
# Package: access.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0908",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0908_allowed = false
policy_0908_allowed if {
    data.policies.access.enabled
}
policy_0908_allowed if {
    input.user.active
    input.resource.public
}
policy_0908_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
