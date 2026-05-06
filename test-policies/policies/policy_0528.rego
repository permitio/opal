package access.validation.resource.check.data.policy_0528

# Auto-generated policy 528 (Rego v1 syntax)
# Package: access.validation.resource.check.data

# Metadata
metadata := {
    "policy_id": "0528",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0528_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0528_allowed if {
    data.policies.access.enabled
}
default policy_0528_allowed = false
