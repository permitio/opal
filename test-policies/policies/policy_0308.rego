package governance.enforcement.context.check.core.policy_0308

# Auto-generated policy 308 (Rego v1 syntax)
# Package: governance.enforcement.context.check.core

# Metadata
metadata := {
    "policy_id": "0308",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0308_allowed if {
    input.user.active
    input.resource.public
}
policy_0308_allowed if {
    data.policies.governance.enabled
}
policy_0308_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0308_allowed if {
    input.user.role == "admin"
}
