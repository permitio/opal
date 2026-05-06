package security.authentication.policy.deny.policy_0167

# Auto-generated policy 167 (Rego v1 syntax)
# Package: security.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0167",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0167_allowed if {
    data.policies.security.enabled
}
default policy_0167_allowed = false
policy_0167_allowed if {
    input.user.active
    input.resource.public
}
