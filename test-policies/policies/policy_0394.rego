package governance.enforcement.action.deny.policy_0394

# Auto-generated policy 394 (Rego v1 syntax)
# Package: governance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0394",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0394_allowed if {
    data.policies.governance.enabled
}
default policy_0394_allowed = false
policy_0394_allowed if {
    input.user.role == "admin"
}
policy_0394_allowed if {
    input.user.active
    input.resource.public
}
