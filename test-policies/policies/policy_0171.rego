package governance.enforcement.user.allow.core.policy_0171

# Auto-generated policy 171 (Rego v1 syntax)
# Package: governance.enforcement.user.allow.core

# Metadata
metadata := {
    "policy_id": "0171",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0171_allowed if {
    data.policies.governance.enabled
}
policy_0171_allowed if {
    input.user.active
    input.resource.public
}
policy_0171_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0171_allowed if {
    input.user.role == "admin"
}
