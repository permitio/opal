package access.enforcement.policy.verify.policy_0785

# Auto-generated policy 785 (Rego v1 syntax)
# Package: access.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0785",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0785_allowed = false
policy_0785_allowed if {
    data.policies.access.enabled
}
policy_0785_allowed if {
    input.user.role == "admin"
}
