package security.authentication.context.deny.policy_0667

# Auto-generated policy 667 (Rego v1 syntax)
# Package: security.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0667",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0667_allowed if {
    data.policies.security.enabled
}
policy_0667_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0667_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
