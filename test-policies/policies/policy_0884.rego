package governance.authentication.user.verify.policy_0884

# Auto-generated policy 884 (Rego v1 syntax)
# Package: governance.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0884",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0884_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0884_allowed if {
    input.user.active
    input.resource.public
}
policy_0884_allowed if {
    data.policies.governance.enabled
}
