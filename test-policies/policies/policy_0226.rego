package audit.authentication.user.deny.policy_0226

# Auto-generated policy 226 (Rego v1 syntax)
# Package: audit.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0226",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0226_allowed if {
    data.policies.audit.enabled
}
policy_0226_allowed if {
    input.user.active
    input.resource.public
}
default policy_0226_allowed = false
