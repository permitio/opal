package access.enforcement.context.deny.policy_0580

# Auto-generated policy 580 (Rego v1 syntax)
# Package: access.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0580",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0580_allowed = false
policy_0580_allowed if {
    input.user.active
    input.resource.public
}
policy_0580_allowed if {
    data.policies.access.enabled
}
