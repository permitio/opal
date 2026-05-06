package access.validation.policy.verify.policy_0772

# Auto-generated policy 772 (Rego v1 syntax)
# Package: access.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0772",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0772_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0772_allowed if {
    data.policies.access.enabled
}
