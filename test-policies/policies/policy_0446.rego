package audit.authentication.action.check.policy_0446

# Auto-generated policy 446 (Rego v1 syntax)
# Package: audit.authentication.action.check

# Metadata
metadata := {
    "policy_id": "0446",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0446_allowed if {
    input.user.role == "admin"
}
policy_0446_allowed if {
    data.policies.audit.enabled
}
policy_0446_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0446_allowed if {
    input.user.active
    input.resource.public
}
