package access.enforcement.policy.allow.policy_0468

# Auto-generated policy 468 (Rego v1 syntax)
# Package: access.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0468",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0468_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0468_allowed if {
    data.policies.access.enabled
}
policy_0468_allowed if {
    input.user.active
    input.resource.public
}
