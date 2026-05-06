package access.enforcement.context.deny.data.policy_0070

# Auto-generated policy 70 (Rego v1 syntax)
# Package: access.enforcement.context.deny.data

# Metadata
metadata := {
    "policy_id": "0070",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0070_allowed if {
    data.policies.access.enabled
}
default policy_0070_allowed = false
