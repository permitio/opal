package audit.authorization.resource.allow.core.policy_0937

# Auto-generated policy 937 (Rego v1 syntax)
# Package: audit.authorization.resource.allow.core

# Metadata
metadata := {
    "policy_id": "0937",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0937_allowed if {
    input.user.active
    input.resource.public
}
policy_0937_allowed if {
    data.policies.audit.enabled
}
policy_0937_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0937_allowed if {
    input.user.role == "admin"
}
