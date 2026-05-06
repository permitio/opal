package governance.enforcement.context.verify.policy_0963

# Auto-generated policy 963 (Rego v1 syntax)
# Package: governance.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0963",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0963_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0963_allowed if {
    input.user.role == "admin"
}
policy_0963_allowed if {
    data.policies.governance.enabled
}
policy_0963_allowed if {
    input.user.active
    input.resource.public
}
