package access.enforcement.user.deny.policy_0645

# Auto-generated policy 645 (Rego v1 syntax)
# Package: access.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0645",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0645_allowed if {
    input.user.role == "admin"
}
policy_0645_allowed if {
    input.user.active
    input.resource.public
}
policy_0645_allowed if {
    data.policies.access.enabled
}
default policy_0645_allowed = false
