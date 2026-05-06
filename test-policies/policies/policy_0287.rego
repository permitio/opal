package governance.monitoring.policy.verify.policy_0287

# Auto-generated policy 287 (Rego v1 syntax)
# Package: governance.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0287",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0287_allowed if {
    input.user.active
    input.resource.public
}
policy_0287_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
